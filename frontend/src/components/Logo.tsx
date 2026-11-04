import { Link } from 'react-router-dom';
import { APP_NAME } from '../config';
import logoImg from '../assets/logo.png';

/** Emblem image. `tile` puts it on a white rounded tile (needed on dark backgrounds). */
export function LogoMark({ size = 28, tile = false }: { size?: number; tile?: boolean }) {
  return (
    <img
      src={logoImg}
      alt=""
      width={size}
      height={size}
      style={{
        objectFit: 'contain',
        flexShrink: 0,
        ...(tile
          ? { background: '#fff', borderRadius: 10, padding: 2 }
          : { mixBlendMode: 'multiply' }),
      }}
    />
  );
}

export function Wordmark({ large = false, tagline = false }: { large?: boolean; tagline?: boolean }) {
  return (
    <span className={`wordmark${large ? ' wordmark--lg' : ''}`}>
      <LogoMark size={large ? 84 : 46} />
      <span className="wordmark__text">
        <span>
          {APP_NAME.slice(0, 5)}
          <b>{APP_NAME.slice(5)}</b>
        </span>
        {tagline && <small className="wordmark__tag">A Better Direction for a Better Earth</small>}
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
