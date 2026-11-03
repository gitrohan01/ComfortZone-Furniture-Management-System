const products = [
  {
    title: "Luxury Sofa",
    price: "$499",
    img: "https://images.unsplash.com/photo-1493663284031-b7e3aefcae8e?w=500",
  },
  {
    title: "Wooden Chair",
    price: "$129",
    img: "https://images.unsplash.com/photo-1519947486511-46149fa0a254?w=500",
  },
  {
    title: "Dining Table",
    price: "$699",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=500",
  },
];

export default function Products() {
  return (
    <section className="section">

      <h2>Best Selling Products</h2>

      <div className="grid">

        {products.map((p) => (
          <div className="product" key={p.title}>

            <img src={p.img} alt={p.title} />

            <h3>{p.title}</h3>

            <p>{p.price}</p>

            <button>Add To Cart</button>

          </div>
        ))}

      </div>

    </section>
  );
}