# Go Arithmetic API

A simple, containerized microservice that provides basic arithmetic operations via a REST API. Built with Go and designed to run on Kubernetes.

## Overview

This service demonstrates a cloud-native Go application pattern that can be deployed on Kubernetes. It provides four arithmetic operations (addition, subtraction, multiplication, and division) through REST API endpoints.

### Features

- RESTful API for arithmetic operations
- JSON request/response format
- Input validation and error handling
- Health check endpoint for Kubernetes probes
- Containerized with multi-stage Docker build
- Production-ready Kubernetes manifests
- Graceful shutdown handling
- Prometheus metrics (`/metrics` endpoint)
- Structured JSON logging (compatible with Loki)
- Observability stack: Prometheus + Loki + Grafana (pre-configured)

## API Endpoints

All arithmetic endpoints accept POST requests with JSON bodies.

### Request Format

```json
{
  "a": 10,
  "b": 5
}
```

### Response Format

**Success Response:**
```json
{
  "result": 15
}
```

**Error Response:**
```json
{
  "error": "error message"
}
```

### Endpoints

#### Addition
```
POST /api/add
```
Returns the sum of two numbers.

Example:
```bash
curl -X POST http://localhost:8080/api/add \
  -H "Content-Type: application/json" \
  -d '{"a": 10, "b": 5}'
```

Response: `{"result": 15}`

#### Subtraction
```
POST /api/subtract
```
Returns the difference (first number minus second number).

Example:
```bash
curl -X POST http://localhost:8080/api/subtract \
  -H "Content-Type: application/json" \
  -d '{"a": 10, "b": 5}'
```

Response: `{"result": 5}`

#### Multiplication
```
POST /api/multiply
```
Returns the product of two numbers.

Example:
```bash
curl -X POST http://localhost:8080/api/multiply \
  -H "Content-Type: application/json" \
  -d '{"a": 10, "b": 5}'
```

Response: `{"result": 50}`

#### Division
```
POST /api/divide
```
Returns the quotient (first number divided by second number).

Example:
```bash
curl -X POST http://localhost:8080/api/divide \
  -H "Content-Type: application/json" \
  -d '{"a": 10, "b": 5}'
```

Response: `{"result": 2}`

Note: Division by zero returns an error: `{"error": "division by zero is not allowed"}`

#### Health Check
```
GET /health
```
Returns the health status of the service.

Example:
```bash
curl http://localhost:8080/health
```

Response: `{"status": "healthy"}`

## Docker

### Build the Docker Image

```bash
docker build -t go-arithmetic-api:latest .
```

The Dockerfile uses a multi-stage build:
- **Build stage:** Uses `golang:1.26` to compile the Go application
- **Runtime stage:** Uses `alpine:latest` for a minimal ~10MB final image

### Run the Docker Container

```bash
docker run -p 8080:8080 go-arithmetic-api:latest
```

The application will be available at `http://localhost:8080`.

### Environment Variables

- `PORT`: Server port (default: 8080)

Example with custom port:
```bash
docker run -e PORT=3000 -p 3000:3000 go-arithmetic-api:latest
```

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (minikube, kind, or cloud provider)
- kubectl configured to access your cluster

### Deploy to Kubernetes

1. Build and load the Docker image (for local clusters like minikube/kind):
   ```bash
   docker build -t go-arithmetic-api:latest .

   # For minikube:
   minikube image load go-arithmetic-api:latest

   # For kind:
   kind load docker-image go-arithmetic-api:latest
   ```

2. Apply the Kubernetes manifests:
   ```bash
   kubectl apply -f k8s/deployment.yaml
   kubectl apply -f k8s/service.yaml
   ```

3. Verify the deployment:
   ```bash
   kubectl get pods
   kubectl get svc
   ```

4. Access the service:
   - **LoadBalancer:** Wait for external IP to be assigned
     ```bash
     kubectl get svc arithmetic-api
     ```
   - **NodePort (if changed):** Access via `http://<node-ip>:<node-port>`
   - **Minikube:** Use `minikube service arithmetic-api`

### Changing Service Type

The default service type is `LoadBalancer`, which works on cloud providers but may not work on local clusters.

#### Option 1: NodePort (for local clusters)

Edit `k8s/service.yaml`:
```yaml
spec:
  type: NodePort  # Changed from LoadBalancer
  selector:
    app: arithmetic-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
    nodePort: 30080  # Optional: specify port (range: 30000-32767)
    name: http
```

Apply the changes:
```bash
kubectl apply -f k8s/service.yaml
```

Access via `http://<node-ip>:30080`

#### Option 2: ClusterIP (internal only)

Edit `k8s/service.yaml`:
```yaml
spec:
  type: ClusterIP  # Changed from LoadBalancer
  selector:
    app: arithmetic-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
    name: http
```

Apply the changes:
```bash
kubectl apply -f k8s/service.yaml
```

Access via port-forwarding:
```bash
kubectl port-forward svc/arithmetic-api 8080:80
```

Then access at `http://localhost:8080`

### Resource Configuration

The deployment includes:
- **CPU Request:** 100m
- **CPU Limit:** 200m
- **Memory Request:** 64Mi
- **Memory Limit:** 128Mi

These can be adjusted in `k8s/deployment.yaml` based on your workload requirements.

### Health Probes

- **Liveness Probe:** Checks `/health` every 10 seconds (restarts pod if failing)
- **Readiness Probe:** Checks `/health` every 5 seconds (removes from service if failing)

## Observability Stack (Prometheus + Loki + Grafana)

The `k8s/monitoring/` directory contains all manifests for the observability stack, deployed in the `monitoring` namespace.

### Deploy the monitoring stack

```bash
kubectl apply -f k8s/monitoring/
```

This creates:
- **Prometheus** — scrapes `/metrics` from the arithmetic API every 15s
- **Loki** — log aggregation backend (single-binary, local storage)
- **Grafana** — pre-configured with Prometheus and Loki datasources and a built-in dashboard

### Access Grafana

```bash
kubectl port-forward svc/grafana 3000:3000 -n monitoring
```

Open `http://localhost:3000` — login with `admin` / `admin`.

The **Arithmetic API** dashboard is available immediately with:
- Request rate per endpoint
- Error rate (5xx)
- P50 / P95 latency
- Application log panel (Loki)

### Access Prometheus

```bash
kubectl port-forward svc/prometheus 9090:9090 -n monitoring
```

Open `http://localhost:9090` — verify the `arithmetic-api` scrape target shows **UP** under Status → Targets.

### Metrics endpoint

The app exposes Prometheus metrics directly:

```bash
curl http://localhost:8080/metrics
```

Key metrics:
- `http_requests_total{method, path, status_code}` — request counter
- `http_request_duration_seconds{method, path}` — latency histogram

### Notes

- Loki and Prometheus use `emptyDir` storage — data is lost on pod restart. For persistent storage, add PersistentVolumeClaims.
- Promtail runs as a DaemonSet (one pod per node) and ships all pod logs to Loki automatically. Logs appear in the Grafana **Application Logs** panel.

## Local Development

### Prerequisites

- Go 1.26 or later

### Run Locally

```bash
go run main.go
```

The server will start on port 8080 (or the port specified in the `PORT` environment variable).

### Run Tests

```bash
go test ./...
```

## Project Structure

```
.
├── handlers/               # HTTP handlers for each endpoint
│   ├── arithmetic.go       # Arithmetic operation handlers
│   └── health.go           # Health check handler
├── middleware/             # HTTP middleware
│   ├── metrics.go          # Prometheus metrics middleware
│   ├── logging.go          # Structured JSON logging middleware
│   └── recorder.go         # Shared response status recorder
├── models/                 # Request/response models
│   ├── request.go          # OperationRequest struct
│   └── response.go         # SuccessResponse and ErrorResponse structs
├── operations/             # Business logic
│   └── arithmetic.go       # Arithmetic operations (Add, Subtract, Multiply, Divide)
├── k8s/                    # Kubernetes manifests
│   ├── deployment.yaml     # App Deployment
│   ├── service.yaml        # App Service
│   └── monitoring/         # Observability stack
│       ├── namespace.yaml
│       ├── prometheus-config.yaml
│       ├── prometheus-deployment.yaml
│       ├── prometheus-service.yaml
│       ├── loki-config.yaml
│       ├── loki-deployment.yaml
│       ├── loki-service.yaml
│       ├── grafana-datasources.yaml
│       ├── grafana-dashboards-config.yaml
│       ├── grafana-deployment.yaml
│       └── grafana-service.yaml
├── main.go                 # Application entry point and routing
├── Dockerfile              # Multi-stage Docker build
├── .dockerignore           # Docker build exclusions
├── go.mod                  # Go module definition
└── README.md               # This file
```

## Architecture

The application follows a layered architecture:

1. **Handlers Layer** (`handlers/`): HTTP request/response handling
2. **Operations Layer** (`operations/`): Business logic for arithmetic operations
3. **Models Layer** (`models/`): Data structures for requests and responses

This separation makes the code easy to test and maintain.

## Security Notes

- This is a demo application with no authentication or authorization
- For production use, add:
  - Authentication (API keys, OAuth, JWT)
  - Rate limiting
  - Request size limits
  - TLS/HTTPS
  - Network policies in Kubernetes

## License

MIT
