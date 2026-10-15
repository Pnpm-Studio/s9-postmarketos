import { initS9 } from './s9-app.js';
import { useModel } from './s9-manifest.js';
useModel(new URLSearchParams(location.search).get('model'));
initS9('usb' in navigator && window.isSecureContext);
