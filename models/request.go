package models

// OperationRequest represents the request body for arithmetic operations
type OperationRequest struct {
	A float64 `json:"a"`
	B float64 `json:"b"`
}
