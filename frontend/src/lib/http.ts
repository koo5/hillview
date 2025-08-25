import { get } from 'svelte/store';
import { auth, logout } from './auth.svelte';
import {backendUrl} from "$lib/config";
import { addToast } from './toast.svelte';
import { createTokenManager } from './tokenManagerFactory';
import type { TokenManager } from './tokenManager';
import { TokenExpiredError as TokenManagerExpiredError, TokenRefreshError } from './tokenManager';

export interface ApiError extends Error {
  status?: number;
  code?: string;
}

export class TokenExpiredError extends Error implements ApiError {
  status = 401;
  code = 'TOKEN_EXPIRED';
  
  constructor(message = 'Your session has expired. Please log in again.') {
    super(message);
    this.name = 'TokenExpiredError';
  }
}

export class HttpClient {
  private baseURL: string;
  private tokenManager: TokenManager;
  
  constructor(baseURL: string) {
    this.baseURL = baseURL;
    this.tokenManager = createTokenManager();
  }
  
  private async makeRequest(url: string, options: RequestInit = {}): Promise<Response> {
    const fullUrl = url.startsWith('http') ? url : `${this.baseURL}${url}`;
    
    try {
      // Get valid token (will auto-refresh if needed)
      const token = await this.tokenManager.getValidToken();
      
      // Prepare headers
      const headers: Record<string, string> = {
        ...(options.headers as Record<string, string> || {}),
      };
      
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      
      const response = await fetch(fullUrl, {
        ...options,
        headers,
      });
      
      // Handle authentication errors
      if (response.status === 401) {
        console.warn('🢄[HTTP] Received 401 Unauthorized response, attempting token refresh');
        
        try {
          // Try to refresh the token
          const refreshSuccess = await this.tokenManager.refreshToken();
          if (refreshSuccess) {
            // Retry the request with the new token
            const newToken = await this.tokenManager.getValidToken();
            if (newToken) {
              const retryHeaders = {
                ...headers,
                'Authorization': `Bearer ${newToken}`
              };
              
              return await fetch(fullUrl, {
                ...options,
                headers: retryHeaders,
              });
            }
          }
        } catch (refreshError) {
          console.error('🢄[HTTP] Token refresh failed:', refreshError);
        }
        
        // If refresh failed, logout
        console.warn('🢄[HTTP] Token refresh failed, logging out');
        logout('Session expired');
        throw new TokenExpiredError();
      }
      
      return response;
      
    } catch (error) {
      // Handle TokenManager errors
      if (error instanceof TokenManagerExpiredError || error instanceof TokenRefreshError) {
        console.warn('🢄[HTTP] TokenManager error:', error.message);
        logout('Session expired');
        throw new TokenExpiredError();
      }
      
      // Re-throw our custom errors
      if (error instanceof TokenExpiredError) {
        throw error;
      }
      
      // Show toast for network errors
      const errorMessage = error instanceof Error ? error.message : 'Network error';
      addToast(`Network error: ${errorMessage}`, 'error', 8000, 'http');
      
      // Wrap other errors
      const apiError = new Error(errorMessage) as ApiError;
      apiError.status = 0;
      throw apiError;
    }
  }
  
  async get(url: string, options: RequestInit = {}): Promise<Response> {
    return this.makeRequest(url, { ...options, method: 'GET' });
  }
  
  async post(url: string, data?: any, options: RequestInit = {}): Promise<Response> {
    const requestOptions: RequestInit = { ...options, method: 'POST' };
    
    if (data) {
      if (data instanceof FormData) {
        requestOptions.body = data;
      } else {
        requestOptions.headers = {
          'Content-Type': 'application/json',
          ...requestOptions.headers,
        };
        requestOptions.body = JSON.stringify(data);
      }
    }
    
    return this.makeRequest(url, requestOptions);
  }
  
  async put(url: string, data?: any, options: RequestInit = {}): Promise<Response> {
    const requestOptions: RequestInit = { ...options, method: 'PUT' };
    
    if (data) {
      if (data instanceof FormData) {
        requestOptions.body = data;
      } else {
        requestOptions.headers = {
          'Content-Type': 'application/json',
          ...requestOptions.headers,
        };
        requestOptions.body = JSON.stringify(data);
      }
    }
    
    return this.makeRequest(url, requestOptions);
  }
  
  async delete(url: string, data?: any, options: RequestInit = {}): Promise<Response> {
    const requestOptions: RequestInit = { ...options, method: 'DELETE' };
    
    if (data) {
      if (data instanceof FormData) {
        requestOptions.body = data;
      } else {
        requestOptions.headers = {
          'Content-Type': 'application/json',
          ...requestOptions.headers,
        };
        requestOptions.body = JSON.stringify(data);
      }
    }
    
    return this.makeRequest(url, requestOptions);
  }
  
  // Special method for file uploads with progress tracking
  async uploadWithProgress(
    url: string,
    formData: FormData,
    onProgress?: (percent: number) => void
  ): Promise<any> {
    const fullUrl = url.startsWith('http') ? url : `${this.baseURL}${url}`;
    
    try {
      // Get valid token (will auto-refresh if needed)
      const token = await this.tokenManager.getValidToken();
      
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        
        // Progress tracking
        if (onProgress) {
          xhr.upload.addEventListener('progress', (event) => {
            if (event.lengthComputable) {
              const percent = Math.round((event.loaded / event.total) * 100);
              onProgress(percent);
            }
          });
        }
        
        xhr.onload = async () => {
          if (xhr.status === 401) {
            console.warn('🢄[HTTP] Upload received 401, attempting token refresh');
            
            try {
              // Try to refresh the token and retry upload
              const refreshSuccess = await this.tokenManager.refreshToken();
              if (refreshSuccess) {
                const newToken = await this.tokenManager.getValidToken();
                if (newToken) {
                  // Create new request with fresh token
                  const retryXhr = new XMLHttpRequest();
                  
                  if (onProgress) {
                    retryXhr.upload.addEventListener('progress', (event) => {
                      if (event.lengthComputable) {
                        const percent = Math.round((event.loaded / event.total) * 100);
                        onProgress(percent);
                      }
                    });
                  }
                  
                  retryXhr.onload = () => {
                    if (retryXhr.status === 401) {
                      logout('Session expired');
                      reject(new TokenExpiredError());
                      return;
                    }
                    
                    if (retryXhr.status >= 200 && retryXhr.status < 300) {
                      try {
                        const result = JSON.parse(retryXhr.responseText);
                        resolve(result);
                      } catch (e) {
                        resolve(retryXhr.responseText);
                      }
                    } else {
                      const errorMessage = `Upload failed: ${retryXhr.status} ${retryXhr.statusText}`;
                      addToast(`Upload error: ${errorMessage}`, 'error', 8000, 'http');
                      const error = new Error(errorMessage) as ApiError;
                      error.status = retryXhr.status;
                      reject(error);
                    }
                  };
                  
                  retryXhr.onerror = () => {
                    const errorMessage = 'Network error during upload retry';
                    addToast(errorMessage, 'error', 8000, 'http');
                    reject(new Error(errorMessage));
                  };
                  
                  retryXhr.open('POST', fullUrl);
                  retryXhr.setRequestHeader('Authorization', `Bearer ${newToken}`);
                  retryXhr.send(formData);
                  return;
                }
              }
            } catch (refreshError) {
              console.error('🢄[HTTP] Upload token refresh failed:', refreshError);
            }
            
            // If refresh failed, logout
            logout('Session expired');
            reject(new TokenExpiredError());
            return;
          }
          
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const result = JSON.parse(xhr.responseText);
              resolve(result);
            } catch (e) {
              resolve(xhr.responseText);
            }
          } else {
            const errorMessage = `Upload failed: ${xhr.status} ${xhr.statusText}`;
            addToast(`Upload error: ${errorMessage}`, 'error', 8000, 'http');
            const error = new Error(errorMessage) as ApiError;
            error.status = xhr.status;
            reject(error);
          }
        };
        
        xhr.onerror = () => {
          const errorMessage = 'Network error during upload';
          addToast(errorMessage, 'error', 8000, 'http');
          reject(new Error(errorMessage));
        };
        
        xhr.open('POST', fullUrl);
        if (token) {
          xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        }
        xhr.send(formData);
      });
      
    } catch (error) {
      // Handle TokenManager errors
      if (error instanceof TokenManagerExpiredError || error instanceof TokenRefreshError) {
        console.warn('🢄[HTTP] Upload TokenManager error:', error.message);
        logout('Session expired');
        throw new TokenExpiredError();
      }
      
      throw error;
    }
  }
}

// Global HTTP client instance
export const http = new HttpClient(backendUrl);

// Helper function to handle API errors consistently
export function handleApiError(error: unknown): string {
  if (error instanceof TokenExpiredError) {
    return 'Your session has expired. Please log in again.';
  }
  
  if (error instanceof Error) {
    return error.message;
  }
  
  return 'An unexpected error occurred';
}