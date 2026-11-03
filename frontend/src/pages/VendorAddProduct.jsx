
import { useState } from "react";
import { API_BASE_URL } from "../servicess/api";
import "../css/VendorPages.css";
import "../css/VendorAddProduct.css";
import VendorPageNav from "../components/Router/VendorPageNav";

const API_URL = `${API_BASE_URL}/vendor/products/`;

const INITIAL_FORM = {
  name: "",
  description: "",
  category: "",
  price: "",
  quantity: "",
};

export default function VendorAddProduct() {
  const [form, setForm] = useState(INITIAL_FORM);
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function handleChange(event) {
    const { name, value } = event.target;

    setForm((previous) => ({
      ...previous,
      [name]: value,
    }));
  }

  function handleImageChange(event) {
    const file = event.target.files?.[0];

    if (!file) return;

    if (!file.type.startsWith("image/")) {
      setError("Please select a valid image file.");
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      setError("Image size must be less than 5 MB.");
      return;
    }

    setError("");
    setImage(file);
    setPreview(URL.createObjectURL(file));
  }

  async function handleSubmit(event) {
    event.preventDefault();

    setMessage("");
    setError("");

    const token =
      localStorage.getItem("access") ||
      localStorage.getItem("token");

    if (!token) {
      setError("Please log in before adding a product.");
      return;
    }

    setLoading(true);

    try {
      const productData = new FormData();

      productData.append("name", form.name.trim());
      productData.append("description", form.description);
      productData.append("category", form.category);
      productData.append("price", form.price);
      productData.append("quantity", form.quantity);

      if (image) {
        productData.append("image", image);
      }

      const response = await fetch(API_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: productData,
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const details = Object.entries(data)
          .map(([field, errors]) => {
            const text = Array.isArray(errors)
              ? errors.join(", ")
              : typeof errors === "object" && errors !== null
                ? JSON.stringify(errors)
                : String(errors);

            return `${field}: ${text}`;
          })
          .join(" | ");

        throw new Error(
          details ||
            data.detail ||
            `Failed to save product (${response.status}).`
        );
      }

      setMessage(
        data.message ||
          `Product "${data.product?.name || data.name || form.name}" added successfully!`
      );

      setForm({ ...INITIAL_FORM });
      setImage(null);
      setPreview("");

      event.target.reset();
    } catch (err) {
      console.error("Add product error:", err);

      setError(
        err.message ||
          "Unable to connect to the server. Please try again."
      );
    } finally {
      setLoading(false);
    }
  }

  function clearForm() {
    setForm({ ...INITIAL_FORM });
    setImage(null);
    setPreview("");
    setMessage("");
    setError("");
  }

  return (
    <div className="vendor-product-page">
      <div className="vendor-product-container">
        <div className="vendor-product-heading">
          <div>
            <span className="vendor-eyebrow">
              VENDOR DASHBOARD
            </span>
            <h1>Add New Product</h1>
            <p>
              Add furniture to your showroom and manage your stock.
            </p>
          </div>

          <div className="vendor-heading-icon">🪑</div>
        </div>

        <VendorPageNav />

        {message && (
          <div
            className="vendor-alert vendor-success"
            role="status"
          >
            ✓ {message}
          </div>
        )}

        {error && (
          <div
            className="vendor-alert vendor-error"
            role="alert"
          >
            {error}
          </div>
        )}

        <form
          onSubmit={handleSubmit}
          className="vendor-product-form"
        >
          <div className="vendor-form-section">
            <h2>Product Information</h2>
            <p className="vendor-section-description">
              Enter the basic details of your furniture product.
            </p>

            <div className="vendor-field">
              <label htmlFor="product-name">
                Product Name *
              </label>
              <input
                id="product-name"
                name="name"
                value={form.name}
                onChange={handleChange}
                placeholder="e.g. Modern Wooden Sofa"
                maxLength={200}
                required
              />
            </div>

            <div className="vendor-field">
              <label htmlFor="product-description">
                Description
              </label>
              <textarea
                id="product-description"
                name="description"
                value={form.description}
                onChange={handleChange}
                placeholder="Describe the material, design, and features..."
                rows={4}
              />
            </div>

            <div className="vendor-field">
              <label htmlFor="product-category">
                Category *
              </label>
              <select
                id="product-category"
                name="category"
                value={form.category}
                onChange={handleChange}
                required
              >
                <option value="">Select a category</option>
                <option value="Sofa">Sofa</option>
                <option value="Bed">Bed</option>
                <option value="Teapoi">Teapoi</option>
                <option value="Chair">Chair</option>
                <option value="Wardrobe">Wardrobe</option>
                <option value="Dining">Dining</option>
                <option value="Dressing Table">
                  Dressing Table
                </option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>

          <div className="vendor-form-section">
            <h2>Pricing & Stock</h2>
            <p className="vendor-section-description">
              Set your selling price and available inventory.
            </p>

            <div className="vendor-fields-grid">
              <div className="vendor-field">
                <label htmlFor="product-price">
                  Price (₹) *
                </label>
                <input
                  id="product-price"
                  name="price"
                  type="number"
                  value={form.price}
                  onChange={handleChange}
                  placeholder="e.g. 15999"
                  min="0.01"
                  step="0.01"
                  required
                />
              </div>

              <div className="vendor-field">
                <label htmlFor="product-quantity">
                  Stock Quantity *
                </label>
                <input
                  id="product-quantity"
                  name="quantity"
                  type="number"
                  value={form.quantity}
                  onChange={handleChange}
                  placeholder="e.g. 25"
                  min="0"
                  step="1"
                  required
                />
              </div>
            </div>
          </div>

          <div className="vendor-form-section">
            <h2>Product Image</h2>
            <p className="vendor-section-description">
              Upload a clear furniture photo (maximum 5 MB).
            </p>

            <label className="vendor-upload-area">
              {preview ? (
                <img
                  className="vendor-image-preview"
                  src={preview}
                  alt="Selected furniture preview"
                />
              ) : (
                <>
                  <span className="vendor-upload-icon">↑</span>
                  <strong>
                    Click to upload product image
                  </strong>
                  <span>PNG, JPG, WEBP — up to 5 MB</span>
                </>
              )}

              <input
                type="file"
                accept="image/*"
                onChange={handleImageChange}
              />
            </label>

            {image && (
              <button
                type="button"
                className="vendor-remove-image"
                onClick={() => {
                  setImage(null);
                  setPreview("");
                }}
              >
                Remove image
              </button>
            )}
          </div>

          <div className="vendor-form-actions">
            <button
              type="button"
              className="vendor-reset-button"
              onClick={clearForm}
              disabled={loading}
            >
              Clear Form
            </button>

            <button
              type="submit"
              className="vendor-submit-button"
              disabled={loading}
            >
              {loading
                ? "Saving Product..."
                : "+ Add Product"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
