<script>
</script>
<div class="inset-gradient top"></div>
<div class="inset-gradient bottom"></div>
<div class="inset-gradient left"></div>
<div class="inset-gradient right"></div>

<style>

	.inset-gradient {
		pointer-events: none;
		position: fixed;


		z-index: 1000000;
		background: linear-gradient(to var(--direction),
		/*#689F38,*/
		rgba(104, 159, 56, 1),
		/*#8BC34A,*/
		rgba(104, 159, 56, 0.9),
		transparent);
	}

	.inset-gradient.top {
		--direction: bottom;
		top: 0;
		left: 0;
		width: 100%;
		height: var(--safe-area-inset-bottom, 0px);
	}

	.inset-gradient.bottom {
		--direction: top;
		bottom: 0;
		left: 0;
		width: 100%;
		height: var(--safe-area-inset-bottom, 0px);
	}

	.inset-gradient.left {
		--direction: right;
		top: 0;
		left: 0;
		width: var(--safe-area-inset-left, 0px);
		height: 100%;
	}

	.inset-gradient.right {
		--direction: left;
		top: 0;
		right: 0;
		width: var(--safe-area-inset-right, 0px);
		height: 100%;
	}

</style>
