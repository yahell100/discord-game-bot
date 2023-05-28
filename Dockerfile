# Use the Python base image
FROM python:3.9-slim-buster

# Set the working directory
WORKDIR /app

# Copy the source code
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set the entrypoint command
CMD ["python", "run.py"]
