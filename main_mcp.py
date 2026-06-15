"""MCP Server 启动入口（stdio 传输）。

MCP Host 侧（如 Claude Desktop）配置示例：
{
  "mcpServers": {
    "port-warehouse": {
      "command": "python",
      "args": ["/path/to/wh_graphrag_re/main_mcp.py"]
    }
  }
}
"""
from src.mcp_server.server import main

if __name__ == "__main__":
    main()
