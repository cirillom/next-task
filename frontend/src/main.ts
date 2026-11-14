import { mount } from 'svelte';
import App from './App.svelte';
import './styles.css';
import { installValidationMessages } from './lib/validation';

installValidationMessages();
mount(App, { target: document.getElementById('app')! });

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'));
}

