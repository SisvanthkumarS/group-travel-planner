import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/AuthProvider';
import {
  validateSignIn,
  type FieldErrors,
  type SignInFields,
} from '../auth/session';
import { AuthLayout } from '../components/AuthLayout';
import { Field } from '../components/Field';

type LocationState = { from?: string } | null;

function SignInHero() {
  return (
    <>
      <div className="auth__copy">
        <h1 className="auth__headline">Plan it together. Decide it once.</h1>
        <p className="auth__lede">
          Everyone suggests activities, the group votes, and the winners land on
          one shared itinerary.
        </p>
      </div>
      <div className="ticket" aria-hidden="true">
        <div className="ticket__main">
          <span className="ticket__eyebrow">ACTIVITY · VOTING OPEN</span>
          <span className="ticket__title">Sunset sail on the Tagus</span>
          <span className="ticket__meta">SAT MAR 15 · 18:30</span>
        </div>
        <div className="ticket__stub">
          <span className="ticket__score">3–1</span>
          <span className="ticket__label">yes / no</span>
        </div>
      </div>
    </>
  );
}

export function SignInPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as LocationState)?.from ?? '/trips';

  const [fields, setFields] = useState<SignInFields>({
    identifier: '',
    password: '',
  });
  const [errors, setErrors] = useState<FieldErrors<SignInFields>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const update = (key: keyof SignInFields) => (value: string) =>
    setFields((current) => ({ ...current, [key]: value }));

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validateSignIn(fields);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      await signIn(fields.identifier, fields.password);
      navigate(from, { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setFormError('Incorrect email, username or password.');
      } else {
        setFormError(
          error instanceof Error ? error.message : 'Sign in failed. Try again.',
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout hero={<SignInHero />}>
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <div className="auth-form__intro">
          <h2 className="auth-form__title">Sign in</h2>
          <p className="auth-form__subtitle">
            Welcome back. Your trips are waiting.
          </p>
        </div>

        {formError && (
          <div className="form-error" role="alert">
            {formError}
          </div>
        )}

        <Field
          label="Email or username"
          name="identifier"
          autoComplete="username"
          value={fields.identifier}
          onChange={(e) => update('identifier')(e.target.value)}
          error={errors.identifier}
        />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={fields.password}
          onChange={(e) => update('password')(e.target.value)}
          error={errors.password}
        />

        <button
          type="submit"
          className="btn btn--primary btn--block"
          disabled={submitting}
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="auth-form__switch">
          New here? <Link to="/register">Create an account</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
