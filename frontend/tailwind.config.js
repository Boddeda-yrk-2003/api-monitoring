/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        ink: {
          900: '#070B16',
          850: '#0A0F1E',
          800: '#0E1526',
          700: '#141C31',
          600: '#1B2540',
        },
        brand: {
          400: '#818CF8',
          500: '#6366F1',
          600: '#4F46E5',
        },
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(129,140,248,0.18), 0 18px 40px -20px rgba(79,70,229,0.55)',
        card: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 20px 45px -30px rgba(0,0,0,0.9)',
      },
      keyframes: {
        pulseRing: {
          '0%': { transform: 'scale(0.8)', opacity: '0.8' },
          '100%': { transform: 'scale(2.2)', opacity: '0' },
        },
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-1000px 0' },
          '100%': { backgroundPosition: '1000px 0' },
        },
      },
      animation: {
        pulseRing: 'pulseRing 2s cubic-bezier(0.4,0,0.6,1) infinite',
        fadeUp: 'fadeUp .35s ease-out both',
        shimmer: 'shimmer 2.4s linear infinite',
      },
    },
  },
  plugins: [],
}
