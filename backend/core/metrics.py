"""
Prometheus metrics instrumentation for Agentic-DataLab.
"""
from prometheus_client import Counter, Histogram, Gauge, Info
import time
from functools import wraps

# Request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

# Agent metrics
agent_executions_total = Counter(
    'agent_executions_total',
    'Total agent executions',
    ['agent_type', 'status']
)

agent_execution_duration_seconds = Histogram(
    'agent_execution_duration_seconds',
    'Agent execution duration in seconds',
    ['agent_type']
)

# Active sessions
active_sessions = Gauge(
    'active_sessions',
    'Number of active user sessions'
)

# Application info
app_info = Info('app', 'Application information')
app_info.info({
    'version': '1.0.0',
    'name': 'Agentic-DataLab'
})


def track_agent_execution(agent_type: str):
    """Decorator to track agent execution metrics."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = 'success'
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'
                raise
            finally:
                duration = time.time() - start_time
                agent_executions_total.labels(agent_type=agent_type, status=status).inc()
                agent_execution_duration_seconds.labels(agent_type=agent_type).observe(duration)
        return wrapper
    return decorator
