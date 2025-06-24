FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY . .

# Create log directory
RUN mkdir -p /var/log/sms_receiver

# Expose the SMS receiver port
EXPOSE 8002

# Run the SMS receiver
CMD ["python", "app.py"]
