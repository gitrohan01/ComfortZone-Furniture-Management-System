export default function ProductCard({product}){

return(

<div className="card">

<img src={product.image} className="card-img-top"/>

<div className="card-body">

<h5>{product.name}</h5>

<p>${product.price}</p>

<button className="btn btn-primary">

Add To Cart

</button>

</div>

</div>

)

}