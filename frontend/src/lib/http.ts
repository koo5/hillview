import { get } from 'svelte/store';
import { auth, logout, checkTokenValidity } from './auth.svelte';
import {backendUrl} from "$lib/config";

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
  
  constructor(baseURL: string) {
    this.baseURL = baseURL;
  }
  
  private async makeRequest(url: string, options: RequestInit = {}): Promise<Response> {
    // Always check token validity before making requests
    if (!checkTokenValidity()) {
      throw new TokenExpiredError();
    }
    
    const authState = get(auth);
    const fullUrl = url.startsWith('http') ? url : `${this.baseURL}${url}`;
    
    // Automatically add auth header if we have a token
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string> || {}),
    };
    
    if (authState.token) {
      headers['Authorization'] = `Bearer ${authState.token}`;
    }
    
    try {
      const response = await fetch(fullUrl, {
        ...options,
        headers,
      });
      
      // Handle authentication errors globally
      if (response.status === 401) {
        console.warn('[HTTP] Received 401 Unauthorized response');
        logout('Session expired');
        throw new TokenExpiredError();
      }
      
      return response;
    } catch (error) {
      // Re-throw our custom errors
      if (error instanceof TokenExpiredError) {
        throw error;
      }
      
      // Wrap other errors
      const apiError = new Error(error instanceof Error ? error.message : 'Network error') as ApiError;
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
  
  async delete(url: string, options: RequestInit = {}): Promise<Response> {
    return this.makeRequest(url, { ...options, method: 'DELETE' });
  }
  
  // Special method for file uploads with progress tracking
  async uploadWithProgress(
    url: string,
    formData: FormData,
    onProgress?: (percent: number) => void
  ): Promise<any> {
    if (!checkTokenValidity()) {
      throw new TokenExpiredError();
    }
    
    const authState = get(auth);
    const fullUrl = url.startsWith('http') ? url : `${this.baseURL}${url}`;
    
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
      
      xhr.onload = () => {
        if (xhr.status === 401) {
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
          const error = new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`) as ApiError;
          error.status = xhr.status;
          reject(error);
        }
      };
      
      xhr.onerror = () => {
        reject(new Error('Network error during upload'));
      };
      
      xhr.open('POST', fullUrl);
      if (authState.token) {
        xhr.setRequestHeader('Authorization', `Bearer ${authState.token}`);
      }
      xhr.send(formData);
    });
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