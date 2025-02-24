import {DMS} from "tsgeo/Formatter/Coordinate/DMS";
import {Coordinate} from "tsgeo/Coordinate";

let formatter = new DMS();

formatter.setSeparator(", ")
    .useCardinalLetters(true)
    .setUnits(DMS.UNITS_ASCII);

export function dms(coord: Coordinate): string {
    return formatter.format(coord);
}
