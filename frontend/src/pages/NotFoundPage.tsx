import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <main className="page">
      <h1 className="page__title">Page not found</h1>
      <p className="page__subtitle">
        That link doesn't go anywhere.{' '}
        <Link to="/trips">Back to your trips</Link>
      </p>
    </main>
  );
}
