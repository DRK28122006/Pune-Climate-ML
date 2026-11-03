import { Link } from 'react-router-dom';
import { APP_NAME } from '../config';

/** Temporary logo: city/canopy split disc plus a text wordmark. Not an official asset. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg viewBox="0 0 200 200" width={size} height={size} aria-hidden="true" focusable="false">
      <circle cx="100" cy="100" r="96" fill="#5b6b73" />
      <path d="M100,4 A96,96 0 0 1 100,196 A48,48 0 0 1 100,100 A48,48 0 0 0 100,4 Z" fill="#2e7d4f" />
      <circle cx="100" cy="52" r="13" fill="#2e7d4f" />
      <circle cx="100" cy="148" r="13" fill="#5b6b73" />
    </svg>
  );
}

export function Wordmark({ large = false }: { large?: boolean }) {
  return (
    <span className={`wordmark${large ? ' wordmark--lg' : ''}`}>
      <LogoMark size={large ? 56 : 28} />
      <span>
        {APP_NAME.slice(0, 5)}
        <b>{APP_NAME.slice(5)}</b>
      </span>
    </span>
  );
}

export default function Logo({ to = '/' }: { to?: string }) {
  return (
    <Link to={to} className="logo-link" aria-label={`${APP_NAME} home`}>
      <Wordmark />
    </Link>
  );
}
