import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import api from '../api';
import { normalizeAuthorization } from './authorization';

const AuthorizationContext = createContext({
  authorization: { status: 'anonymous', isStaff: false, permissions: new Set() },
  reloadAuthorization: async () => null,
});

function initialAuthorization() {
  return localStorage.getItem('access')
    ? { status: 'loading', isStaff: false, permissions: new Set() }
    : { status: 'anonymous', isStaff: false, permissions: new Set() };
}

export function AuthorizationProvider({ children }) {
  const [authorization, setAuthorization] = useState(initialAuthorization);
  const requestId = useRef(0);

  const reloadAuthorization = useCallback(async () => {
    const currentRequestId = ++requestId.current;
    if (!localStorage.getItem('access')) {
      const anonymous = { status: 'anonymous', isStaff: false, permissions: new Set() };
      setAuthorization(anonymous);
      return anonymous;
    }

    setAuthorization({ status: 'loading', isStaff: false, permissions: new Set() });
    try {
      const response = await api.get('auth/permissions/');
      if (currentRequestId !== requestId.current || !localStorage.getItem('access')) {
        return { status: 'anonymous', isStaff: false, permissions: new Set() };
      }
      const normalized = normalizeAuthorization(response.data);
      const next = normalized || { status: 'unavailable', isStaff: false, permissions: new Set() };
      setAuthorization(next);
      return next;
    } catch (error) {
      if (currentRequestId !== requestId.current) {
        return { status: 'anonymous', isStaff: false, permissions: new Set() };
      }
      if (!localStorage.getItem('access') || error.response?.status === 401) {
        const anonymous = { status: 'anonymous', isStaff: false, permissions: new Set() };
        setAuthorization(anonymous);
        return anonymous;
      }
      const unavailable = { status: 'unavailable', isStaff: false, permissions: new Set() };
      setAuthorization(unavailable);
      return unavailable;
    }
  }, []);

  useEffect(() => {
    const reload = () => { void reloadAuthorization(); };
    const clear = () => {
      requestId.current += 1;
      setAuthorization({ status: 'anonymous', isStaff: false, permissions: new Set() });
    };
    window.addEventListener('auth:changed', reload);
    window.addEventListener('auth:refreshed', reload);
    window.addEventListener('auth:expired', clear);
    window.addEventListener('auth:logout', clear);
    if (localStorage.getItem('access')) reload();
    return () => {
      window.removeEventListener('auth:changed', reload);
      window.removeEventListener('auth:refreshed', reload);
      window.removeEventListener('auth:expired', clear);
      window.removeEventListener('auth:logout', clear);
    };
  }, [reloadAuthorization]);

  const value = useMemo(() => ({ authorization, reloadAuthorization }), [
    authorization, reloadAuthorization,
  ]);
  return <AuthorizationContext.Provider value={value}>{children}</AuthorizationContext.Provider>;
}

export function useAuthorization() {
  return useContext(AuthorizationContext);
}
