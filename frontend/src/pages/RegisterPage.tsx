import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/AuthProvider';
import {
  MIN_PASSWORD_LENGTH,
  registerConflictField,
  validateRegister,
  type FieldErrors,
  type RegisterFields,
} from '../auth/session';
import { AuthLayout } from '../components/AuthLayout';
import { Field } from '../components/Field';

function RegisterHero() {
  return (
    <>
      <div className="auth__copy">
        <h1 className="auth__headline">
          One trip. One plan. Everyone gets a vote.
        </h1>
        <ol className="steps">
          <li>
            <span className="steps__num">01</span>Create a trip or accept an
            invite
          </li>
          <li>
            <span className="steps__num">02</span>Propose activities with a time
            and a cost
          </li>
          <li>
            <span className="steps__num">03</span>Vote, and winners join the
            itinerary
          </li>
        </ol>
      </div>
      <span className="auth__footnote">Up to 8 travelers per trip.</span>
    </>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [fields, setFields] = useState<RegisterFields>({
    user_name: '',
    email: '',
    password: '',
  });
  const [errors, setErrors] = useState<FieldErrors<RegisterFields>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const update = (key: keyof RegisterFields) => (value: string) =>
    setFields((current) => ({ ...current, [key]: value }));

  const passwordLongEnough = fields.password.length >= MIN_PASSWORD_LENGTH;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validateRegister(fields);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      await register(fields);
      navigate('/trips', { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        const field = registerConflictField(error.message);
        if (field) setErrors({ [field]: error.message });
        else setFormError(error.message);
      } else if (error instanceof ApiError && error.status === 422) {
        setErrors(error.fieldErrors as FieldErrors<RegisterFields>);
        setFormError(
          Object.keys(error.fieldErrors).length ? null : error.message,
        );
      } else {
        setFormError(
          error instanceof Error
            ? error.message
            : 'Registration failed. Try again.',
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout hero={<RegisterHero />}>
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <div className="auth-form__intro">
          <h2 className="auth-form__title">Create your account</h2>
          <p className="auth-form__subtitle">
            Takes a minute. Your group finds you by email or username.
          </p>
        </div>

        {formError && (
          <div className="form-error" role="alert">
            {formError}
          </div>
        )}

        <Field
          label="Username"
          name="user_name"
          autoComplete="username"
          maxLength={30}
          value={fields.user_name}
          onChange={(e) => update('user_name')(e.target.value)}
          error={errors.user_name}
        />
        <Field
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          value={fields.email}
          onChange={(e) => update('email')(e.target.value)}
          error={
            errors.email &&
            (registerConflictField(errors.email) === 'email' ? (
              <>
                {errors.email} <Link to="/sign-in">Sign in instead</Link>
              </>
            ) : (
              errors.email
            ))
          }
        />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          value={fields.password}
          onChange={(e) => update('password')(e.target.value)}
          error={errors.password}
          hint={
            <span
              className={passwordLongEnough ? 'field__hint--ok' : undefined}
            >
              {passwordLongEnough && (
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M5 12l5 5L19 7" />
                </svg>
              )}
              At least {MIN_PASSWORD_LENGTH} characters
            </span>
          }
        />

        <button
          type="submit"
          className="btn btn--primary btn--block"
          disabled={submitting}
        >
          {submitting ? 'Creating account…' : 'Create account'}
        </button>

        <p className="auth-form__switch">
          Already have an account? <Link to="/sign-in">Sign in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
