import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import api from "../servicess/api";

export default function CatalogCategory({
    category,
    title,
    sectionClass,
    gridClass,
    cardClass,
    detailsClass,
    fallbackImages = [],
}) {
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const navigate = useNavigate();

    useEffect(() => {
        let active = true;
        api.get("products/").then((response) => {
            if (!active) return;
            const categoryProducts = response.data.filter(
                (product) => product.category?.trim().toLowerCase() === category.toLowerCase(),
            );
            setProducts(categoryProducts);
            setError("");
        }).catch(() => {
            if (active) setError("Unable to load this collection.");
        }).finally(() => {
            if (active) setLoading(false);
        });
        return () => { active = false; };
    }, [category]);

    return (
        <section className={sectionClass}>
            <h2>{title}</h2>
            {loading && <p className="info">Loading collection...</p>}
            {error && <p className="info" role="alert">{error}</p>}
            {!loading && !error && products.length === 0 && (
                <p className="info">No {category.toLowerCase()} products are available yet.</p>
            )}
            <div className={gridClass}>
                {products.map((product, index) => (
                    <article className={cardClass} key={product.id}>
                        <img
                            src={product.image_url || product.image || fallbackImages[index % fallbackImages.length]}
                            alt={product.name}
                        />
                        <div className={detailsClass}>
                            <h3>{product.name}</h3>
                            <p className="info">{product.description}</p>
                            <span className="discount">
                                {product.quantity > 0 ? `Available: ${product.quantity}` : "Out of Stock"}
                            </span>
                            <div className="price">
                                <span className="new-price">
                                    ₹{Number(product.price).toLocaleString("en-IN", {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2,
                                    })}
                                </span>
                            </div>
                            <button
                                type="button"
                                disabled={product.quantity <= 0}
                                onClick={() => navigate(`/product/${product.id}`)}
                            >
                                {product.quantity > 0 ? "Buy Now" : "Out of Stock"}
                            </button>
                        </div>
                    </article>
                ))}
            </div>
        </section>
    );
}
