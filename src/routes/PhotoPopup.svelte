<script>
let { photo } = $props();
</script>

<div class="popup">

<img src={photo.url} alt="Photo" style="max-width: 200px; max-height: 200px;"/>
<pre>


    {JSON.stringify(photo, null, 2)}


</pre>
</div>

<style>
.popup {
    overflow: scroll;
    max-height: 300px;
}
    </style>
