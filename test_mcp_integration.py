#!/usr/bin/env python3
"""
Comprehensive MCP integration test for TradeXV2 DataLake module.
Tests all MCP tools and resources that don't require external dependencies.
"""

import asyncio
from datalake.mcp.server import create_server


async def test_all_functionality():
    """Test all MCP tools and resources."""
    print("=" * 60)
    print("TradeXV2 DataLake MCP Integration Test")
    print("=" * 60)
    
    # Create server
    server = create_server()
    print("✓ MCP Server created successfully")
    
    # List available tools and resources
    tools = await server.list_tools()
    resources = await server.list_resources()
    print(f"✓ Found {len(tools)} tools and {len(resources)} resources")
    
    # Test each tool
    print("\n" + "=" * 30)
    print("Testing Tools")
    print("=" * 30)
    
    # 1. Test datalake_list_rules
    print("\n1. Testing datalake_list_rules...")
    try:
        result = await server.call_tool('datalake_list_rules', {})
        print("✓ SUCCESS - Rules retrieved")
        print(f"  Found {len(result)} rules")
    except Exception as e:
        print(f"✗ FAILED - {e}")
    
    # 2. Test datalake_universe
    print("\n2. Testing datalake_universe...")
    try:
        result = await server.call_tool('datalake_universe', {'universe': 'NIFTY50'})
        print("✓ SUCCESS - Universe retrieved")
        print(f"  Found {len(result)} symbols in NIFTY50")
    except Exception as e:
        print(f"✗ FAILED - {e}")
    
    # 3. Test datalake_history
    print("\n3. Testing datalake_history...")
    try:
        result = await server.call_tool('datalake_history', {
            'symbol': 'RELIANCE', 
            'timeframe': '1D', 
            'days': 5
        })
        print("✓ SUCCESS - Historical data retrieved")
        print(f"  Found {len(result)} data points")
    except Exception as e:
        print(f"✗ FAILED - {e}")
    
    # 4. Test datalake_quality
    print("\n4. Testing datalake_quality...")
    try:
        result = await server.call_tool('datalake_quality', {
            'symbol': 'RELIANCE', 
            'timeframe': '1m'
        })
        print("✓ SUCCESS - Quality report generated")
        print(f"  Status: {result[0].text}")
    except Exception as e:
        print(f"✗ FAILED - {e}")
    
    # Test resources
    print("\n" + "=" * 30)
    print("Testing Resources")
    print("=" * 30)
    
    # 1. Test schema resource
    print("\n1. Testing datalake://schema resource...")
    try:
        result = await server.read_resource('datalake://schema')
        print("✓ SUCCESS - Schema retrieved")
        print(f"  Schema includes {len(result)} content items")
    except Exception as e:
        print(f"✗ FAILED - {e}")
    
    # 2. Test rules resource
    print("\n2. Testing datalake://rules resource...")
    try:
        result = await server.read_resource('datalake://rules')
        print("✓ SUCCESS - Rules retrieved")
        print(f"  Rules include {len(result)} content items")
    except Exception as e:
        print(f"✗ FAILED - {e}")
    
    print("\n" + "=" * 60)
    print("MCP Integration Test Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_all_functionality())