import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from src.warehouse.models import WorkOrder, OrderItem, TaskType, OrderPriority


@pytest.fixture
def mock_parser():
    mock_inst = WorkOrder(
        order_id=1,
        source="vlm",
        priority=OrderPriority.NORMAL,
        items=[OrderItem(
            item_id=1,
            task_type=TaskType.OUTBOUND,
            part_name="轴承",
            quantity=3,
        )],
    )
    parser = MagicMock()
    parser.parse.return_value = mock_inst
    return parser


@pytest.fixture
def mock_inv_db():
    db = MagicMock()
    db.query.return_value = None
    db.query_by_name.return_value = MagicMock(
        model="M100", location="Mech1_R1_B1", quantity=5,
        available=5, en_name="Bearing"
    )
    db.reserve.return_value = "Mech1_R1_B1"
    return db


@pytest.fixture
def app(mock_inv_db):
    from src.api.app import create_app
    from src.api.queue_manager import OrderQueue
    from collections import OrderedDict
    app = create_app(
        inv_db=mock_inv_db,
        vlm_available=False,
    )
    # ASGITransport 不触发 lifespan，手动初始化 state 用于测试
    app.state.inv_db           = mock_inv_db
    app.state.vlm_available    = False
    app.state.queue            = OrderQueue()
    app.state.results          = OrderedDict()
    app.state.state_meta       = {
        "last_run_id": None,
        "last_run_at": None,
        "scheduler_status": "idle",
        "inv_db": mock_inv_db,
    }
    return app


@pytest.mark.asyncio
async def test_post_instructions_returns_queued(app):
    mock_order = WorkOrder(
        order_id=1,
        source="vlm",
        priority=OrderPriority.NORMAL,
        items=[OrderItem(
            item_id=1,
            task_type=TaskType.OUTBOUND,
            part_name="轴承",
            quantity=3,
            resolved_pick="Mech1_R1_B1",
            resolved_dest="PORT_OUT_1",
        )],
    )
    with patch("src.warehouse.wms.order_manager.OrderManager.from_port_instruction",
               return_value=mock_order) as mock_from_instruction:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/instructions", json={"text": "需要3个轴承出库"}
            )
    assert app.state.queue.size() == 1
    assert mock_from_instruction.call_args.kwargs["inventory_db"] is app.state.inv_db
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["parsed"][0]["part_name"] == "轴承"


@pytest.mark.asyncio
async def test_post_audio_only_transcribes_and_queues_in_rule_fallback(app):
    mock_order = WorkOrder(
        order_id=1,
        source="vlm",
        priority=OrderPriority.NORMAL,
        items=[OrderItem(
            item_id=1,
            task_type=TaskType.OUTBOUND,
            part_name="轴承",
            quantity=2,
            resolved_pick="Mech1_R1_B1",
            resolved_dest="PORT_OUT_1",
        )],
    )
    with patch("src.api.app._transcribe_audio_base64", return_value="需要2个轴承出库") as mock_asr, \
         patch("src.warehouse.wms.order_manager.OrderManager.from_port_instruction",
               return_value=mock_order) as mock_from_instruction:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/instructions", json={"audio_base64": "AAAA"}
            )

    assert resp.status_code == 200
    assert app.state.queue.size() == 1
    assert mock_asr.called
    assert mock_from_instruction.call_args.args[0].description == "需要2个轴承出库"


def test_process_order_urgent_delegates_without_bound_self():
    from src.api import celery_app

    with patch.object(celery_app.process_order, "run", return_value={"status": "completed"}) as mock_run:
        result = celery_app.process_order_urgent.run("紧急出库", None, "inst-1")

    assert result == {"status": "completed"}
    mock_run.assert_called_once_with("紧急出库", None, "inst-1")


@pytest.mark.asyncio
async def test_get_status_returns_queue_info(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/status")
    assert resp.status_code == 200
    assert "queue_size" in resp.json()


@pytest.mark.asyncio
async def test_get_result_unknown_id_returns_404(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/result/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_empty_body_returns_400(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/instructions", json={})
    assert resp.status_code == 400
