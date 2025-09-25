import { get } from 'svelte/store';
import { auth, logout } from './auth.svelte';
import {backendUrl} from "$lib/config";
import { showNetworkError } from './alertSystem.svelte';
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
  private tokenManager: TokenManager | null = null;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
  }

  private getTokenManager(): TokenManager {
    if (!this.tokenManager) {
      this.tokenManager = createTokenManager();
    }
    return this.tokenManager;
  }

  private async makeRequest(url: string, options: RequestInit = {}): Promise<Response> {
    const fullUrl = url.startsWith('http') ? url : `${this.baseURL}${url}`;

    try {
      // Get valid token (will auto-refresh if needed)
      const token = await this.getTokenManager().getValidToken();

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
        // Only attempt refresh if we actually sent an auth token that was rejected
        if (token) {
          console.warn('🢄[HTTP] Received 401 Unauthorized response, attempting token refresh');

          try {
            // Get fresh token with force refresh (backend rejected the previous token)
            const newToken = await this.getTokenManager().getValidToken(true);
            if (newToken && newToken !== token) {
              const retryHeaders = {
                ...headers,
                'Authorization': `Bearer ${newToken}`
              };

              return await fetch(fullUrl, {
                ...options,
                headers: retryHeaders,
              });
            }
          } catch (refreshError) {
            console.error('🢄[HTTP] Token refresh failed:', refreshError);
          }

        // If refresh failed, logout
        console.warn('🢄[HTTP] Token refresh failed, logging out');
        logout('Session expired');
        throw new TokenExpiredError();
        } else {
          // No token was sent, so this is just an unauthenticated request to a protected endpoint
          // Don't attempt refresh or logout, just return the 401 response
        }
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
      showNetworkError(`Network error: ${errorMessage}`, 'http');

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
