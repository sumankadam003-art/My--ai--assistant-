import * as SecureStore from 'expo-secure-store';
import API_URL from './apiConfig';

const TOKEN_KEY = 'neha_access_token';

export async function getChallenge() {
  if (!API_URL) throw new Error('API address is not configured.');
  const response = await fetch(`${API_URL}/auth/challenge`, { method: 'POST' });
  const data = await response.json();
  if (!response.ok || !data.success || !data.challenge_id) {
    throw new Error(data.error || 'Could not start login.');
  }
  return { challengeId: String(data.challenge_id), challenge: String(data.challenge), expiresIn: 120 };
}

export async function login(challengeId: string, answer: string) {
  if (!API_URL) throw new Error('API address is not configured.');
  const response = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ challenge_id: challengeId, answer }),
  });
  const data = await response.json();
  if (!response.ok || !data.success || !data.access_token) {
    throw new Error(data.error || 'Login failed. Generate a fresh challenge and try again.');
  }
  await SecureStore.setItemAsync(TOKEN_KEY, data.access_token);
  return true;
}

export async function getAccessToken() {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function logout() {
  const token = await getAccessToken();
  if (token && API_URL) {
    try {
      await fetch(`${API_URL}/auth/logout`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` },
      });
    } finally {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    }
  } else {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
  }
}
