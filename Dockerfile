FROM python:3.12-slim

# libyaz5: native Z39.50 library (Index Data)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libyaz5 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 MCP_PORT=8000
EXPOSE 8000
USER nobody
CMD ["spain-libraries-mcp"]
