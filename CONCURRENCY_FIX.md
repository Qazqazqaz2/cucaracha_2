# Concurrency Fix for Database Operations

This document explains the concurrency issue that was fixed in the indexer and how it was resolved.

## Problem Description

The original code was experiencing a concurrency issue with database operations, resulting in the following error:

```
asyncpg.exceptions._base.InterfaceError: cannot perform operation: another operation is in progress
```

This error occurred because multiple async operations were trying to use the same database connection simultaneously.

## Root Cause

The issue was in the [run_indexer](file://c:\Users\armian\Desktop\Works\cryptoExchange\indexator.py#L314-L367) function where:

1. A single database connection was being shared among multiple concurrent operations
2. The jetton verification workers and pool verification workers were all trying to use the same connection
3. When one worker was performing a database operation, other workers would get the "another operation is in progress" error

## Solution

The solution involved modifying the code to ensure each concurrent operation has its own database connection:

### 1. Separate Connections for Workers

Instead of sharing a single connection, each worker now creates its own connection:

```python
async def worker(addr):
    async with sem:
        # Create a new connection for each worker to avoid concurrency issues
        worker_conn = await asyncpg.connect(db_dsn)
        try:
            await verify_jetton_onchain(ton_client, worker_conn, addr)
        finally:
            await worker_conn.close()
```

### 2. Main Connection Management

The main connection is now properly managed within each indexing cycle:

```python
async def run_indexer(db_dsn: str):
    await init_db(db_dsn)

    # Create connection for each cycle
    conn = await asyncpg.connect(db_dsn)
    try:
        # ... perform main operations ...
    finally:
        # Close connection at the end of each cycle
        await conn.close()
```

### 3. Pool Worker Connections

Pool workers also create their own connections:

```python
async def pool_worker(pr):
    async with sem2:
        # Create a new connection for each worker to avoid concurrency issues
        worker_conn = await asyncpg.connect(db_dsn)
        try:
            await verify_pool_reserves_onchain(ton_client, worker_conn, pr)
            await worker_conn.execute("UPDATE pools SET last_checked = now() WHERE id=$1", pr["id"])
        finally:
            await worker_conn.close()
```

## Benefits of This Solution

1. **Eliminates Concurrency Issues**: Each operation has its own dedicated database connection
2. **Better Resource Management**: Connections are properly closed after use
3. **Improved Performance**: Operations can run truly in parallel without blocking each other
4. **Error Prevention**: Prevents the "another operation is in progress" error
5. **Scalability**: Can handle more concurrent operations without issues

## Testing

A test script [test_concurrent_db.py](file:///c%3A/Users/armian/Desktop/Works/cryptoExchange/test_concurrent_db.py) was created to verify that concurrent database operations work correctly with the new approach.

## Additional Considerations

1. **Connection Pooling**: While this solution works, in a production environment you might want to consider using connection pooling for better resource utilization
2. **Error Handling**: The solution includes proper error handling and connection cleanup
3. **Resource Limits**: The semaphore limits still apply to prevent overwhelming the database with too many concurrent connections