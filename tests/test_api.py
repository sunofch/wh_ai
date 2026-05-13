import pytest
from unittest.mock import MagicMock
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
def app(mock_parser, mock_inv_db):
    from src.api.app import create_app
    from src.api.queue_manager import OrderQueue
    from collections import OrderedDict
    app = create_app(
        parser=mock_parser,
        inv_db=mock_inv_db,
        vlm_available=True,
    )
    # ASGITransport 不触发 lifespan，手动初始化 state 用于测试
    app.state.parser           = mock_parser
    app.state.inv_db           = mock_inv_db
    app.state.vlm_available    = True
    app.state.queue            = OrderQueue()
    app.state.results          = OrderedDict()
    app.state.last_run_id      = None
    app.state.last_run_at      = None
    app.state.scheduler_status = "idle"
    return app


@pytest.mark.asyncio
async def test_post_instructions_returns_queued(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/instructions", json={"text": "需要3个轴承出库"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["parsed"]["part_name"] == "轴承"


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
