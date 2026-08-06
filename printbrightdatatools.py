import asyncio
import os

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()


async def main():
    token = os.getenv("BRIGHT_DATA_API_KEY") or os.getenv("BRIGHTDATA_TOKEN")

    if not token:
        raise ValueError("BRIGHTDATA_TOKEN not found in .env")

    client = MultiServerMCPClient(
        {
            "bright_data": {
                "transport": "streamable_http",
                "url": f"https://mcp.brightdata.com/mcp?token={token}",
            }
        }
    )

    tools = await client.get_tools()

    print(f"\nFound {len(tools)} tools\n")
    print(tools)

    for i, tool in enumerate(tools, 1):
        print("=" * 80)
        print(f"Tool {i}")
        print(f"Name        : {tool.name}")
        print(f"Description : {tool.description}")

        # Print input schema if available
        if hasattr(tool, "args_schema") and tool.args_schema:
            print("\nArguments:")
            try:
                schema = tool.args_schema.model_json_schema()

                for name, info in schema.get("properties", {}).items():
                    required = name in schema.get("required", [])
                    print(
                        f"  • {name}"
                        f"{' (required)' if required else ''}"
                        f" : {info.get('type', 'unknown')}"
                    )

            except Exception as e:
                print(f"Could not parse schema: {e}")

        print()

if __name__ == "__main__":
    asyncio.run(main())