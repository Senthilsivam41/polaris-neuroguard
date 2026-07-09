/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'cyber-navy': '#0B0F19',
        'midnight-surface': '#161D30',
        'accent-cyan': '#00E5FF',
        'alert-crimson': '#FF3366',
      },
    },
  },
  plugins: [],
}
