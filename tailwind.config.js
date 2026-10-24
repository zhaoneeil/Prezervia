/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
    './lib/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        cream: '#FDFBF7',
        stravaOrange: '#FC4C02',
        alertOrange: '#FF7A00',
        alertRed: '#D32F2F',
        aliceBlue: '#F0F8FF',
        saturatedBlue: '#004AAD',
        ink: '#F4EEE6',
        bark: '#B3A394',
        sand: '#3B302A',
        pasture: '#2F6F4E',
      },
      fontFamily: {
        display: ['Alice', 'Georgia', 'Cambria', 'serif'],
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          '"Segoe UI"',
          'Roboto',
          '"Helvetica Neue"',
          'Arial',
          'sans-serif',
        ],
      },
      boxShadow: {
        soft: '0 1px 0 rgba(255,255,255,0.05) inset, 0 12px 32px -12px rgba(0,0,0,0.55)',
        lift: '0 24px 48px -16px rgba(0,0,0,0.7)',
      },
      borderColor: {
        DEFAULT: 'rgba(255,255,255,0.10)',
      },
      keyframes: {
        pulseRing: {
          '0%': { boxShadow: '0 0 0 0 rgba(211, 47, 47, 0.45)' },
          '100%': { boxShadow: '0 0 0 14px rgba(211, 47, 47, 0)' },
        },
      },
      animation: {
        pulseRing: 'pulseRing 1.6s ease-out infinite',
      },
    },
  },
  plugins: [],
};
