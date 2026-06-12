import os
import h2o

# Clear proxy variables
for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
    os.environ.pop(key, None)

print("Starting H2O...")
try:
    h2o.init(
        ip="127.0.0.1",
        port=54321,
        max_mem_size="2G",
        nthreads=-1,
        proxy=None,
        bind_to_localhost=True,
        verbose=True,
    )
    print("H2O Started Successfully.")
except Exception as e:
    print(f"H2O failed: {e}")
