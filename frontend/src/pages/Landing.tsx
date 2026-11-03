import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { Wordmark } from '../components/Logo';
import { TAGLINE } from '../config';
import { useAtmosphere } from '../scene/atmosphereStore';
import { useReducedMotion } from '../lib/useAsync';

export default function Landing() {
  // The landing page shows the left-to-right story (polluted to green) as pure scenery.
  // The scene's greenness value stays at 0: no optimization has happened yet.
  useAtmosphere(0, true, true);
  const navigate = useNavigate();
  const reduce = useReducedMotion();
  const [leaving, setLeaving] = useState(false);

  const go = () => {
    if (reduce) return navigate('/assess');
    setLeaving(true);
    window.setTimeout(() => navigate('/assess'), 550);
  };

  return (
    <main id="main" className={`landing${leaving ? ' is-leaving' : ''}`}>
      <div className="landing__top">
        <Wordmark large />
        <Link to="/dashboard/overview" className="landing__dash">
          Open dashboard
        </Link>
      </div>

      <div className="landing__hero">
        <h1 className="halo">{TAGLINE}</h1>
        <div className="lede lede--card">
          <p>
            DishaDharti helps planners evaluate an urban plan, optimize it against heat, air quality, green cover and
            flood risk, and see the greener outcome. Prototype city: Pune.
          </p>
          <p className="note">Prototype. All figures shown in this app are simulated demonstration data.</p>
        </div>
      </div>

      <div className="landing__cta">
        <button type="button" className="btn btn--primary btn--lg cta" onClick={go}>
          Evaluate
          <ArrowRight size={20} aria-hidden="true" />
        </button>
        <span className="cta__hint halo">Start with your plan's inputs</span>
        <div className="guide">
          <span className="guide__text halo">Build a Better City</span>
          <svg className="guide__arrow" viewBox="0 0 240 30" aria-hidden="true" focusable="false">
            <defs>
              <linearGradient id="guide-grad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0" stopColor="#5b6b73" />
                <stop offset="1" stopColor="#2e7d4f" />
              </linearGradient>
            </defs>
            <path className="guide__line" d="M3 17 C 70 7, 130 25, 222 15" pathLength="1" />
            <path className="guide__head" d="M211 6 L226 15 L212 25" />
          </svg>
        </div>
      </div>
      <div className="wipe" aria-hidden="true" />
    </main>
  );
}
