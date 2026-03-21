package models

// SuccessResponse represents a successful operation response
type SuccessResponse struct {
	Result float64 `json:"result"`
}

// ErrorResponse represents an error response
type ErrorResponse struct {
	Error string `json:"error"`
}
