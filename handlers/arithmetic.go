package handlers

import (
	"encoding/json"
	"go-arithmetic-api/models"
	"go-arithmetic-api/operations"
	"log/slog"
	"net/http"
	"os"
)

// AddHandler handles addition requests
func AddHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req models.OperationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, "Invalid input: "+err.Error(), http.StatusBadRequest)
		return
	}

	result := operations.Add(req.A, req.B)
	respondWithSuccess(w, result)
}

// SubtractHandler handles subtraction requests
func SubtractHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req models.OperationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, "Invalid input: "+err.Error(), http.StatusBadRequest)
		return
	}

	result := operations.Subtract(req.A, req.B)
	respondWithSuccess(w, result)
}

// MultiplyHandler handles multiplication requests
func MultiplyHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req models.OperationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, "Invalid input: "+err.Error(), http.StatusBadRequest)
		return
	}

	result := operations.Multiply(req.A, req.B)
	respondWithSuccess(w, result)
}

// DivideHandler handles division requests
func DivideHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req models.OperationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, "Invalid input: "+err.Error(), http.StatusBadRequest)
		return
	}

	if req.B == 0 {
		slog.Error("FATAL: division by zero - crashing pod", "a", req.A, "b", req.B)
		os.Exit(1)
	}

	result, err := operations.Divide(req.A, req.B)
	if err != nil {
		respondWithError(w, err.Error(), http.StatusBadRequest)
		return
	}

	respondWithSuccess(w, result)
}

// respondWithSuccess sends a successful JSON response
func respondWithSuccess(w http.ResponseWriter, result float64) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(models.SuccessResponse{Result: result})
}

// respondWithError sends an error JSON response
func respondWithError(w http.ResponseWriter, message string, statusCode int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	json.NewEncoder(w).Encode(models.ErrorResponse{Error: message})
}
