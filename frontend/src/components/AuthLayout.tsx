import type { ReactNode } from 'react';
import { BrandMark } from './BrandMark';

/** Split screen for sign-in and register: brand panel left, form right. */
export function AuthLayout({
  hero,
  children,
}: {
  hero: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="auth">
      <section className="auth__hero">
        <div className="auth__brand">
          <BrandMark light size={32} />
          <span>Group Travel Planner</span>
        </div>
        {hero}
      </section>
      <main className="auth__panel">{children}</main>
    </div>
  );
}
