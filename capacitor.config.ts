import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.prezervia.app',
  appName: 'Prezervia',
  webDir: 'out',
  backgroundColor: '#17110e',
  ios: { contentInset: 'never', backgroundColor: '#17110e' },
  plugins: {
    SplashScreen: { backgroundColor: '#17110e', launchShowDuration: 1200, showSpinner: false },
    StatusBar: { style: 'DARK', backgroundColor: '#17110e' },
  },
};

export default config;
