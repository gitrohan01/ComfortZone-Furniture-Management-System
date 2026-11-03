
// frontend/src/pages/VendorProfile.jsx

import { useCallback, useEffect, useState } from "react";
import api from "../servicess/api";
import { useNavigate } from "react-router-dom";
import "../css/VendorPages.css";
import VendorPageNav from "../components/Router/VendorPageNav";

const API = "vendor/profile/";

const getHeaders = () => {
  const token =
    localStorage.getItem("access") || localStorage.getItem("token");
  return { Authorization: `Bearer ${token}` };
};

const emptyForm = {
  business_name: "",
  phone: "",
  address: "",
  city: "",
  description: "",
};

function VendorProfile() {
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const navigate = useNavigate();

  const loadProfile = useCallback(async () => {
    const token =
      localStorage.getItem("access") || localStorage.getItem("token");

    if (!token) {
      navigate("/login");
      return;
    }

    try {
      const response = await api.get(API, { headers: getHeaders() });
      const data = response.data;

      setProfile(data);
      setForm({
        business_name: data.business_name || "",
        phone: data.phone || "",
        address: data.address || "",
        city: data.city || "",
        description: data.description || "",
      });
      setError("");
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.message ||
          "Could not load vendor profile. Check the Django profile endpoint."
      );
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    let active = true;
    api.get(API, { headers: getHeaders() }).then((response) => {
      if (!active) return;
      const data = response.data;
      setProfile(data);
      setForm({
        business_name: data.business_name || "",
        phone: data.phone || "",
        address: data.address || "",
        city: data.city || "",
        description: data.description || "",
      });
      setError("");
    }).catch((err) => {
      if (active) setError(err.response?.data?.detail || "Could not load vendor profile.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((previous) => ({ ...previous, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");

    try {
      const response = await api.put(API, form, {
        headers: {
          ...getHeaders(),
          "Content-Type": "application/json",
        },
      });

      setProfile(response.data);
      setForm({
        business_name: response.data.business_name ?? form.business_name,
        phone: response.data.phone ?? form.phone,
        address: response.data.address ?? form.address,
        city: response.data.city ?? form.city,
        description: response.data.description ?? form.description,
      });
      setMessage("Vendor profile updated successfully.");
    } catch (err) {
      const data = err.response?.data;
      const detail =
        typeof data === "string"
          ? data
          : data?.detail ||
            data?.message ||
            (data ? JSON.stringify(data) : "Unable to update vendor profile.");

      setError(detail);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <main className="vendor-page"><p>Loading vendor profile...</p></main>;
  }

  return (
    <main className="vendor-page">
      <div className="vendor-page-header">
        <div>
          <p className="vendor-eyebrow">ACCOUNT SETTINGS</p>
          <h1>Vendor Profile</h1>
          <p>Manage your furniture business details.</p>
        </div>
      </div>

      <VendorPageNav />

      {error && <p className="vendor-alert error">{error}</p>}
      {message && <p className="vendor-alert success">{message}</p>}

      <section className="vendor-panel vendor-profile-panel">
        <div className="vendor-profile-heading">
          <div className="vendor-avatar">
            {(form.business_name || "V").trim().charAt(0).toUpperCase()}
          </div>
          <div>
            <h2>{form.business_name || "Your Business"}</h2>
            <p>{profile?.user?.email || profile?.email || "Vendor account"}</p>
          </div>
        </div>

        <form className="vendor-form" onSubmit={handleSubmit}>
          <label>
            Business Name
            <input
              type="text"
              name="business_name"
              value={form.business_name}
              onChange={handleChange}
              required
            />
          </label>

          <label>
            Phone
            <input
              type="tel"
              name="phone"
              value={form.phone}
              onChange={handleChange}
              required
            />
          </label>

          <label>
            City
            <input
              type="text"
              name="city"
              value={form.city}
              onChange={handleChange}
            />
          </label>

          <label>
            Address
            <textarea
              name="address"
              value={form.address}
              onChange={handleChange}
              rows={3}
            />
          </label>

          <label className="vendor-form-full">
            Business Description
            <textarea
              name="description"
              value={form.description}
              onChange={handleChange}
              rows={4}
            />
          </label>

          <div className="vendor-form-actions">
            <button
              className="vendor-primary-button"
              type="submit"
              disabled={saving}
            >
              {saving ? "Saving..." : "Save Profile"}
            </button>

            <button
              className="vendor-secondary-button"
              type="button"
              onClick={loadProfile}
              disabled={saving}
            >
              Reload
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}

export default VendorProfile;
