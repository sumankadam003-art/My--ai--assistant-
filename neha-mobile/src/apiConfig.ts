const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || 'http://127.0.0.1:8765'
).replace(/\/+$/, '');

export default API_URL;
