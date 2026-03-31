
import createLucideIcon from '../createLucideIcon';
import type { AstroComponent } from '../types'

/**
 * @component @name CirclePile
 * @description Lucide SVG icon component, renders SVG Element with children.
 *
 * @preview ![img](data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiMwMDAiIHN0eWxlPSJiYWNrZ3JvdW5kLWNvbG9yOiAjZmZmOyBib3JkZXItcmFkaXVzOiAycHgiICBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+CiAgPGNpcmNsZSBjeD0iMTIiIGN5PSIxOSIgcj0iMiIgLz4KICA8Y2lyY2xlIGN4PSIxMiIgY3k9IjUiIHI9IjIiIC8+CiAgPGNpcmNsZSBjeD0iMTYiIGN5PSIxMiIgcj0iMiIgLz4KICA8Y2lyY2xlIGN4PSIyMCIgY3k9IjE5IiByPSIyIiAvPgogIDxjaXJjbGUgY3g9IjQiIGN5PSIxOSIgcj0iMiIgLz4KICA8Y2lyY2xlIGN4PSI4IiBjeT0iMTIiIHI9IjIiIC8+Cjwvc3ZnPg==) - https://lucide.dev/icons/circle-pile
 * @see https://lucide.dev/guide/packages/lucide-astro - Documentation
 *
 * @param {import('../types').IconProps} props - Lucide icons props and any valid SVG attribute
 * @returns {any} Astro Component
 * 
 */
const CirclePile = createLucideIcon('circle-pile', [["circle",{"cx":"12","cy":"19","r":"2"}],["circle",{"cx":"12","cy":"5","r":"2"}],["circle",{"cx":"16","cy":"12","r":"2"}],["circle",{"cx":"20","cy":"19","r":"2"}],["circle",{"cx":"4","cy":"19","r":"2"}],["circle",{"cx":"8","cy":"12","r":"2"}]]) as AstroComponent;

export default CirclePile;
