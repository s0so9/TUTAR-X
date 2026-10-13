import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { initNativeChrome } from './native/initNativeChrome'
import './styles/global.css'

void initNativeChrome()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
