import axios from 'axios';
import { shouldExpireSession } from './auth/authorization';

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'
).replace(/\/$/, '');

const api = axios.create({ baseURL: `${API_BASE_URL}/` });
let refreshPromise;

function expireSession() {
  localStorage.removeItem('access');
  localStorage.removeItem('refresh');
  localStorage.removeItem('user');
  window.dispatchEvent(new Event('auth:expired'));
}

api.interceptors.request.use((config) => {
  const access = localStorage.getItem('access');
  if (access) config.headers.Authorization = `Bearer ${access}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const path = String(original?.url || '');
    const isAuthRequest = ['auth/login/', 'auth/refresh/'].some((item) => path.includes(item));
    if (!shouldExpireSession(error) || !original || original._retried || isAuthRequest) {
      return Promise.reject(error);
    }

    const refresh = localStorage.getItem('refresh');
    if (!refresh) {
      expireSession();
      return Promise.reject(error);
    }

    original._retried = true;
    try {
      refreshPromise ||= axios.post(`${API_BASE_URL}/auth/refresh/`, { refresh });
      const response = await refreshPromise;
      localStorage.setItem('access', response.data.access);
      if (response.data.refresh) localStorage.setItem('refresh', response.data.refresh);
      window.dispatchEvent(new Event('auth:refreshed'));
      original.headers = original.headers || {};
      original.headers.Authorization = `Bearer ${response.data.access}`;
      return api(original);
    } catch (refreshError) {
      if (shouldExpireSession(refreshError)) expireSession();
      return Promise.reject(refreshError);
    } finally {
      refreshPromise = undefined;
    }
  },
);

export default api;
