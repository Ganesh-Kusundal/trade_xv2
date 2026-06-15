/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bbg:    'rgb(var(--bbg)    / <alpha-value>)',
        bbg1:   'rgb(var(--bbg-1)  / <alpha-value>)',
        bbg2:   'rgb(var(--bbg-2)  / <alpha-value>)',
        bbg3:   'rgb(var(--bbg-3)  / <alpha-value>)',
        bline:  'rgb(var(--bline)  / <alpha-value>)',
        bline2: 'rgb(var(--bline-2)/ <alpha-value>)',
        bfg:    'rgb(var(--bfg)    / <alpha-value>)',
        bfgm:   'rgb(var(--bfg-m)  / <alpha-value>)',
        bfgd:   'rgb(var(--bfg-d)  / <alpha-value>)',
        bamb:   'rgb(var(--bamb)   / <alpha-value>)',
        bcy:    'rgb(var(--bcy)    / <alpha-value>)',
        bmg:    'rgb(var(--bmg)    / <alpha-value>)',
        bull:   'rgb(var(--bull)   / <alpha-value>)',
        bear:   'rgb(var(--bear)   / <alpha-value>)',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],
        xs:   ['0.6875rem', { lineHeight: '1rem' }],
        sm:   ['0.8125rem', { lineHeight: '1.125rem' }],
        base: ['0.875rem',  { lineHeight: '1.25rem' }],
      },
      boxShadow: {
        panel: '0 0 0 1px rgb(var(--bline) / 0.6), 0 1px 2px 0 rgb(0 0 0 / 0.4)',
      },
      animation: {
        marquee: 'marquee 60s linear infinite',
        'pulse-soft': 'pulseSoft 2s ease-in-out infinite',
        'flash-up': 'flashUp 600ms ease-out',
        'flash-down': 'flashDown 600ms ease-out',
      },
      keyframes: {
        marquee: {
          '0%':   { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0.55' },
        },
        flashUp: {
          '0%':   { backgroundColor: 'rgba(34,197,94,0.4)' },
          '100%': { backgroundColor: 'transparent' },
        },
        flashDown: {
          '0%':   { backgroundColor: 'rgba(239,68,68,0.4)' },
          '100%': { backgroundColor: 'transparent' },
        },
      },
    },
  },
  plugins: [],
}
