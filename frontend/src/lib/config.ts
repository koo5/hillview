import { TAURI_MOBILE } from './tauri';
console.log('🔍🔍 TAURI_MOBILE:', TAURI_MOBILE);


export const geoPicsUrl = import.meta.env.VITE_REACT_APP_GEO_PICS_URL;
export const backendUrl = (TAURI_MOBILE ? import.meta.env.VITE_BACKEND_ANDROID : import.meta.env.VITE_BACKEND) || 'http://localhost:8055';

export const FEATURE_USER_ACCOUNTS = import.meta.env.VITE_FEATURE_USER_ACCOUNTS === 'true' || import.meta.env.VITE_FEATURE_USER_ACCOUNTS === true;