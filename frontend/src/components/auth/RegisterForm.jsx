import React, { useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import styles from "./AuthForm.module.css";

export const RegisterForm = ({ onSuccess }) => {
  const { register } = useAuth();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    email: "",
    first_name: "",
    last_name: "",
    password: "",
    password_confirm: "",
  });
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const updateField = (field, value) => setForm((prev) => ({ ...prev, [field]: value }));

  const handleNext = () => {
    if (!form.email || !form.first_name) {
      setError("Please fill all fields");
      return;
    }
    setError("");
    setStep(2);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (form.password !== form.password_confirm) {
      setError("Passwords do not match");
      return;
    }
    setError("");
    setIsLoading(true);
    try {
      await register(form);
      onSuccess?.();
    } catch (err) {
      const data = err.response?.data;
      setError(data?.email?.[0] || data?.password?.[0] || data?.detail || "Registration failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form className={styles.form} onSubmit={step === 1 ? handleNext : handleSubmit}>
      {step === 1 && (
        <>
          <Input
            label="First name"
            value={form.first_name}
            onChange={(e) => updateField("first_name", e.target.value)}
            placeholder="Allan"
            required
          />
          <Input
            label="Last name"
            value={form.last_name}
            onChange={(e) => updateField("last_name", e.target.value)}
            placeholder="Smith"
          />
          <Input
            label="Email"
            type="email"
            value={form.email}
            onChange={(e) => updateField("email", e.target.value)}
            placeholder="you@example.com"
            required
          />
        </>
      )}
      {step === 2 && (
        <>
          <Input
            label="Password"
            type="password"
            value={form.password}
            onChange={(e) => updateField("password", e.target.value)}
            placeholder="Min. 8 characters"
            required
            showPasswordToggle
          />
          <Input
            label="Confirm password"
            type="password"
            value={form.password_confirm}
            onChange={(e) => updateField("password_confirm", e.target.value)}
            placeholder="Repeat password"
            required
            showPasswordToggle
          />
        </>
      )}
      {error && <div className={styles.error}>{error}</div>}
      <div className={styles.actions}>
        {step === 2 && (
          <Button type="button" variant="ghost" onClick={() => setStep(1)}>
            ← Back
          </Button>
        )}
        <Button type="submit" isLoading={isLoading} fullWidth>
          {step === 1 ? "Continue →" : "Create account →"}
        </Button>
      </div>
    </form>
  );
};