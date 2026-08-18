FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY fixtures ./fixtures
COPY examples ./examples
RUN pip install --no-cache-dir .
EXPOSE 18765
# Default: fixture server. Override with `crashmin ...`.
CMD ["crashmin-fixtures", "--host", "0.0.0.0", "--port", "18765"]
