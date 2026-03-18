/**
 * Utilities for API authentication in Playwright tests
 */

/**
 * Get a JWT token for any user by username and password.
 */
export async function getUserToken(username: string, password: string): Promise<string> {
  const response = await fetch('http://localhost:8055/api/auth/token', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Accept': 'application/json'
    },
    body: new URLSearchParams({
      'username': username,
      'password': password,
      'grant_type': 'password'
    })
  });

  if (!response.ok) {
    throw new Error(`Failed to get token for ${username}: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();
  return data.access_token;
}

/**
 * Get admin token for API testing
 */
export async function getAdminToken(adminPassword: string): Promise<string> {
  return getUserToken('admin', adminPassword);
}

/**
 * Make authenticated API call as admin
 */
export async function callAdminAPI(
  endpoint: string,
  adminPassword: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = await getAdminToken(adminPassword);

  return fetch(`http://localhost:8055${endpoint}`, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
      'Accept': 'application/json'
    }
  });
}