import * as SecureStore from 'expo-secure-store';
import API_URL from './apiConfig';

const TOKEN_KEY = 'neha_access_token';

export async function login(email: string, password: string) {
  if (!API_URL) throw new Error('API address is not configured.');

  const response = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email.trim(), password }),
  });

  const data = await response.json();

  if (!response.ok || !data.success || !data.access_token) {
    throw new Error(data.error || 'Login failed. Check your credentials.');
  }

  await SecureStore.setItemAsync(TOKEN_KEY, data.access_token);
  return true;
}

export async function getAccessToken() {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function logout() {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}
