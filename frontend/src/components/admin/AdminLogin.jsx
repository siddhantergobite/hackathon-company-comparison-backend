import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { Banner, Button, Card } from '../ui';

// Shared sign-in box for the Event and News admin areas (one admin key, kept in sessionStorage).
export default function AdminLogin({ auth, what = 'admin', envName = 'EVENT_ADMIN_API_KEY' }) {
  const [key, setKey] = useState('');
  return (
    <Card className="adm-login">
      <div className="adm-login__icon"><KeyRound size={24} aria-hidden="true" /></div>
      <h2>Admin sign-in</h2>
      <p className="muted">Enter the {what} key (<code>{envName}</code> in your <code>.env</code>).</p>
      {auth.error && <Banner tone="error">{auth.error}</Banner>}
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          if (key.trim()) auth.login(key);
        }}
      >
        <div>
          <label className="form-label" htmlFor="admin-key">Admin key</label>
          <input id="admin-key" className="input" type="password" autoComplete="current-password" value={key} onChange={(e) => setKey(e.target.value)} autoFocus />
        </div>
        <Button type="submit" loading={auth.checking} disabled={!key.trim()}>Sign in</Button>
      </form>
    </Card>
  );
}
