import { initS9 } from './s9-app.js';
initS9('usb' in navigator && window.isSecureContext);
