# MCP Integration Completion Plan

## 🎯 Objective
Complete the missing database-dependent MCP functionality by creating the required database catalog and testing all remaining tools/resources.

## 📋 Current Status
- **Working**: 4/7 tools, 2/2 resources (67% complete)
- **Missing**: 3 tools, 2 resources (33% remaining)
- **Blocker**: Missing `.datalake/catalog.duckdb` database

## 🗂️ Step-by-Step Completion Plan

### Phase 1: Database Setup (Critical Path)
**Goal**: Create the required database catalog with test data

#### Step 1.1: Initialize Database Catalog
```bash
# Create database directory
mkdir -p .datalake

# Initialize empty catalog database
python -c "
import duckdb
conn = duckdb.connect('.datalake/catalog.duckdb')
conn.close()
print('✓ Empty catalog database created')
"
```

#### Step 1.2: Create Required Tables
```python
# Create minimal schema for testing
import duckdb

conn = duckdb.connect('.datalake/catalog.duckdb')

# Create intraday snapshot table (for scanner)
conn.execute('''
CREATE TABLE v_intraday_snapshot (
    symbol TEXT,
    timestamp TIMESTAMP,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume BIGINT,
    rsi_approx DOUBLE,
    roc_5 DOUBLE,
    roc_10 DOUBLE,
    score DOUBLE
)
''')

# Create options analytics tables
conn.execute('''
CREATE TABLE m_pcr (
    underlying TEXT,
    timestamp TIMESTAMP,
    pcr DOUBLE,
    call_oi BIGINT,
    put_oi BIGINT
)
''')

conn.execute('''
CREATE TABLE m_max_pain (
    underlying TEXT,
    timestamp TIMESTAMP,
    max_pain_price DOUBLE,
    max_pain_oi BIGINT
)
''')

conn.execute('''
CREATE TABLE m_iv_surface (
    underlying TEXT,
    timestamp TIMESTAMP,
    strike DOUBLE,
    iv DOUBLE,
    call_iv DOUBLE,
    put_iv DOUBLE
)
''')

# Create data quality table
conn.execute('''
CREATE TABLE data_quality (
    symbol TEXT,
    check_date DATE,
    total_rows BIGINT,
    missing_candles BIGINT,
    duplicate_candles BIGINT,
    completeness_pct DOUBLE,
    status TEXT
)
''')

conn.close()
print('✓ Required tables created')
```

#### Step 1.3: Populate Test Data
```python
# Insert minimal test data
import duckdb
from datetime import datetime

conn = duckdb.connect('.datalake/catalog.duckdb')

# Insert test data for scanner
conn.execute('''
INSERT INTO v_intraday_snapshot VALUES
('RELIANCE', '2026-06-10 09:45:00', 1275.0, 1280.0, 1270.0, 1278.0, 1000000, 65.0, 2.5, 3.0, 100.0),
('TCS', '2026-06-10 09:45:00', 3500.0, 3520.0, 3490.0, 3515.0, 800000, 70.0, 3.2, 4.1, 95.0)
''')

# Insert test data for options
conn.execute('''
INSERT INTO m_pcr VALUES
('NIFTY', '2026-06-10 15:30:00', 1.25, 1000000, 1250000)
''')

# Insert test data for quality
conn.execute('''
INSERT INTO data_quality VALUES
('RELIANCE', '2026-06-10', 1000, 50, 0, 95.0, 'OK'),
('TCS', '2026-06-10', 1200, 100, 5, 91.7, 'WARNING')
''')

conn.close()
print('✓ Test data populated')
```

### Phase 2: Test Database-Dependent Tools
**Goal**: Verify all remaining tools work with the database

#### Step 2.1: Test datalake_scan Tool
```python
import asyncio
from datalake.mcp.server import create_server

async def test_scan():
    server = create_server()
    
    # Test with JSON rule
    rule_json = '{"name": "test_rule", "sql": "SELECT symbol FROM v_intraday_snapshot WHERE rsi_approx > 60 LIMIT 5"}'
    
    result = await server.call_tool('datalake_scan', {
        'rule': rule_json,
        'date': '2026-06-10'
    })
    
    print('Scan result:', result[0].text)
    return result

asyncio.run(test_scan())
```

#### Step 2.2: Test datalake_relative_volume Tool
```python
import asyncio
from datalake.mcp.server import create_server

async def test_rel_volume():
    server = create_server()
    
    result = await server.call_tool('datalake_relative_volume', {
        'date': '2026-06-10',
        'cutoff_time': '09:45',
        'min_rel_volume': 0.5,
        'lookback_days': 5
    })
    
    print('Relative volume result:', result[0].text)
    return result

asyncio.run(test_rel_volume())
```

#### Step 2.3: Test datalake_options Tool
```python
import asyncio
from datalake.mcp.server import create_server

async def test_options():
    server = create_server()
    
    result = await server.call_tool('datalake_options', {
        'underlying': 'NIFTY',
        'analysis_type': 'pcr'
    })
    
    print('Options result:', result[0].text)
    return result

asyncio.run(test_options())
```

### Phase 3: Test Database-Dependent Resources
**Goal**: Verify all remaining resources work with the database

#### Step 3.1: Test datalake://universe/{name} Resource
```python
import asyncio
from datalake.mcp.server import create_server

async def test_universe_resource():
    server = create_server()
    
    result = await server.read_resource('datalake://universe/NIFTY50')
    print('Universe resource result:', result[0].content)
    return result

asyncio.run(test_universe_resource())
```

#### Step 3.2: Test datalake://quality/{date} Resource
```python
import asyncio
from datalake.mcp.server import create_server

async def test_quality_resource():
    server = create_server()
    
    result = await server.read_resource('datalake://quality/2026-06-10')
    print('Quality resource result:', result[0].content)
    return result

asyncio.run(test_quality_resource())
```

### Phase 4: Comprehensive Testing
**Goal**: Run full test suite with all functionality

#### Step 4.1: Update Test Script
```python
# Update test_mcp_integration.py to include database-dependent tests
```

#### Step 4.2: Run Complete Test Suite
```bash
python test_mcp_integration.py
```

#### Step 4.3: Verify All Tools and Resources
```bash
python -c "
import asyncio
from datalake.mcp.server import create_server

async def verify_all():
    server = create_server()
    tools = await server.list_tools()
    resources = await server.list_resources()
    
    print(f'✓ All {len(tools)} tools registered')
    print(f'✓ All {len(resources)} resources registered')
    
    # Test each tool
    for tool in tools:
        print(f'Testing {tool.name}...')
        # Add appropriate test parameters for each tool
        pass

asyncio.run(verify_all())
"
```

### Phase 5: Documentation and Cleanup
**Goal**: Finalize documentation and ensure everything works

#### Step 5.1: Update MCP_INTEGRATION_STATUS.md
```markdown
## 🎉 Completion Status

- **MCP Integration**: ✅ 100% COMPLETE
- **All Tools**: ✅ 7/7 tested and working
- **All Resources**: ✅ 4/4 tested and working
- **Database Setup**: ✅ Complete
```

#### Step 5.2: Create Usage Examples
```python
# Create examples/mcp_usage.py with common usage patterns
```

#### Step 5.3: Final Verification
```bash
# Run final comprehensive test
python test_mcp_integration.py

# Test server can start
python -m datalake.mcp.server --help
```

## 📅 Timeline Estimate
- **Phase 1 (Database Setup)**: 1-2 hours
- **Phase 2 (Tool Testing)**: 1-2 hours
- **Phase 3 (Resource Testing)**: 30-60 minutes
- **Phase 4 (Comprehensive Testing)**: 1-2 hours
- **Phase 5 (Documentation)**: 30-60 minutes

**Total**: 4-8 hours to complete all missing functionality

## 🔧 Requirements
- DuckDB installed (already available)
- MCP package installed (already available)
- Python 3.8+ (already available)
- Basic test data (will be created)

## 🎯 Success Criteria
1. ✅ All 7 tools working and tested
2. ✅ All 4 resources working and tested
3. ✅ Database catalog created with test data
4. ✅ Comprehensive test suite passing
5. ✅ Updated documentation
6. ✅ Usage examples provided

## 🚀 Next Immediate Action
Start with **Phase 1, Step 1.1** - Create the database catalog file and tables.