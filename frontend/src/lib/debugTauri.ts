import { event, path } from '@tauri-apps/api';
import { TAURI, TAURI_MOBILE, TAURI_DESKTOP, isTauriAvailable } from './tauri';

// Debug helper to check Tauri availability
export function debugTauriStatus() {
    console.log('=== TAURI DEBUG INFO ===');
    console.log('TAURI available:', TAURI);
    console.log('TAURI_MOBILE:', TAURI_MOBILE);
    console.log('TAURI_DESKTOP:', TAURI_DESKTOP);
    console.log('window.__TAURI__:', (window as any).__TAURI__);
    console.log('window.__TAURI_INTERNALS__:', (window as any).__TAURI_INTERNALS__);
    console.log('navigator.userAgent:', navigator.userAgent);
    console.log('Is Android:', /Android/i.test(navigator.userAgent));
    
    if ((window as any).__TAURI__) {
        console.log('Tauri modules available:');
        for (const key in (window as any).__TAURI__) {
            console.log(`  - ${key}:`, typeof (window as any).__TAURI__[key]);
        }
    }
    
    // Check if we can import Tauri modules
    if (isTauriAvailable()) {
        import('@tauri-apps/api/core').then(module => {
            console.log('✅ @tauri-apps/api/core imported successfully');
            console.log('Available functions:', Object.keys(module));
        }).catch(err => {
            console.error('❌ Failed to import @tauri-apps/api/core:', err);
        });
    } else {
        console.log('ℹ️ Tauri not available - running in browser mode');
    }
}

// Run debug on page load
if (typeof window !== 'undefined') {
    (window as any).addEventListener('load', () => {
        console.log('🔍 Running Tauri debug on window load');
        debugTauriStatus();
    });
    
    // Also run immediately
    console.log('🔍 Running Tauri debug immediately');
    debugTauriStatus();
}