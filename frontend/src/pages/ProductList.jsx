import {
    useEffect,
    useState
} from "react";

import api from "../servicess/api";
import { useNavigate } from "react-router-dom";


function ProductList({ category }) {

    const [products, setProducts] =
        useState([]);

    const navigate = useNavigate();

    useEffect(() => {
        let active = true;
        api.get("products/").then((response) => {
            if (!active) return;
            const productsForPage = category
                ? response.data.filter((product) => product.category === category)
                : response.data;
            setProducts(productsForPage);
        }).catch(() => {
            if (active) setProducts([]);
        });
        return () => { active = false; };
    }, [category]);


    return (

        <section className="product-section">

            <h2>
                {category
                    ? `${category} Collection`
                    : "Furniture Collection"}
            </h2>


            <div className="product-grid">

                {products.map(
                    product => (

                        <div
                            className="product-card"
                            key={product.id}
                        >

                            <img
                                src={product.image_url || product.image}
                                alt={product.name}
                            />


                            <h3>
                                {product.name}
                            </h3>


                            <p>
                                {product.description}
                            </p>


                            <h3>
                                ₹{product.price}
                            </h3>


                            <p>

                                {product.quantity > 0

                                    ? `Available: ${product.quantity}`

                                    : "Out of Stock"

                                }

                            </p>


                            <button
                                disabled={
                                    product.quantity <= 0
                                }
                                onClick={() =>
                                    navigate(
                                        `/product/${product.id}`
                                    )
                                }
                            >

                                {product.quantity > 0
                                    ? "Buy Now"
                                    : "Out of Stock"
                                }

                            </button>

                        </div>

                    )
                )}

            </div>

        </section>
    );
}

export default ProductList;
