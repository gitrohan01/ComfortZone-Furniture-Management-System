import "../css/Categories.css";

const categories = [
  {
    name: "Living Room",
    img: "https://images.unsplash.com/photo-1493663284031-b7e3aefcae8e?w=500",
  },
  {
    name: "Bedroom",
    img: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=500",
  },
  {
    name: "Office",
    img: "https://images.unsplash.com/photo-1484154218962-a197022b5858?w=500",
  },
];

export default function Categories() {
  return (
    <section className="category-section">

      <h2>Shop By Category</h2>

      <div className="category-grid">

        {categories.map((item) => (
          <div className="category-card" key={item.name}>

            <img 
              src={item.img} 
              alt={item.name} 
            />

            <h3>{item.name}</h3>

          </div>
        ))}

      </div>

    </section>
  );
}