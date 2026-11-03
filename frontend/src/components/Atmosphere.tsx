import { useEffect, useRef } from 'react';
import { createScene, skyBackground, type SceneEngine } from '../scene/engine';
import { atmosphere, useAtmosphereSpatial, useAtmosphereWide } from '../scene/atmosphereStore';
import { useReducedMotion } from '../lib/useAsync';

/** Fixed background: sky, haze, clouds, hills, skyline, growing tree and the rotating city/canopy motif. */
export default function Atmosphere() {
  const reduce = useReducedMotion();
  const wide = useAtmosphereWide();
  const spatial = useAtmosphereSpatial();
  const skyRef = useRef<HTMLDivElement>(null);
  const hazeRef = useRef<HTMLDivElement>(null);
  const fxRef = useRef<HTMLCanvasElement>(null);
  const treeRef = useRef<HTMLCanvasElement>(null);
  const yyRef = useRef<SVGSVGElement>(null);
  const engineRef = useRef<SceneEngine | null>(null);

  useEffect(() => {
    const fx = fxRef.current!, tree = treeRef.current!;
    const engine = createScene(fx, tree, reduce);
    engineRef.current = engine;
    engine.setSpatial(atmosphere.getSpatial());
    engine.resize();
    let cur = atmosphere.getTarget();
    let raf = 0;
    const t0 = performance.now();
    const onResize = () => engine.resize();
    window.addEventListener('resize', onResize);

    const frame = (now: number) => {
      const time = reduce ? 0 : now - t0;
      const target = atmosphere.getTarget();
      cur += (target - cur) * (reduce ? 1 : 0.045);
      if (Math.abs(target - cur) < 0.0005) cur = target;
      const { sky, hazeOpacity } = skyBackground(cur);
      if (skyRef.current) skyRef.current.style.background = sky;
      if (hazeRef.current) hazeRef.current.style.opacity = hazeOpacity.toFixed(3);
      if (yyRef.current) yyRef.current.style.transform = `rotate(${(cur * 720 + time * 0.002).toFixed(2)}deg)`;
      engine.draw(cur, time);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', onResize);
    };
  }, [reduce]);

  // The tree canvas changes width between the landing page and the rest of the app,
  // and the landing page draws the left-to-right version of the scene.
  useEffect(() => {
    engineRef.current?.setSpatial(spatial);
    engineRef.current?.resize();
  }, [wide, spatial]);

  return (
    <div className="atmo" aria-hidden="true">
      <div ref={skyRef} className="atmo__sky" />
      <div ref={hazeRef} className="atmo__haze" />
      <div className={`atmo__dawn${spatial ? ' is-on' : ''}`} />
      <div className={`atmo__smog${spatial ? ' is-on' : ''}`} />
      <canvas ref={fxRef} className="atmo__fx" />
      <div className="atmo__yy">
        <svg ref={yyRef} viewBox="-6 -6 212 212">
          <circle cx="100" cy="100" r="100" fill="var(--city)" />
          <path d="M100,0 A100,100 0 0 1 100,200 A50,50 0 0 1 100,100 A50,50 0 0 0 100,0 Z" fill="var(--leaf)" />
          <circle cx="100" cy="50" r="14" fill="var(--leaf)" />
          <circle cx="100" cy="150" r="14" fill="var(--city)" />
          <circle cx="100" cy="100" r="100" fill="none" stroke="var(--ink)" strokeWidth="1.2" />
        </svg>
      </div>
      <canvas ref={treeRef} className={`atmo__tree${wide ? ' atmo__tree--wide' : ''}`} />
    </div>
  );
}
