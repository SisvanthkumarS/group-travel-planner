const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export async function apiRequest<T>(path: string, token?: string): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}
